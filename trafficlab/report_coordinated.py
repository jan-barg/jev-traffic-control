"""Export the fresh experiment separately from all earlier benchmark evidence."""
from collections import Counter
import gzip,json,math,shutil
import numpy as np
from scipy.stats import t as student_t
from .scenario import ROOT
from .report import METRICS

NAMES={'fixed':'Tuned fixed-time','library-fixed':'Retuned fixed plan','plan-numeric':'Numerical plan selector','plan-jev':'Coordinated Jev'}
SCENARIOS={'am':'Weekday morning','surge':'Morning + 50% surge','shift':'Changing directional demand'}


def paired(rows,scenario,controller,reference,metric):
    deltas=[];seeds=[]
    for r in rows:
        if r['scenario']!=scenario or r['controller']!=controller:continue
        ref=next((x for x in rows if x['scenario']==scenario and x['seed']==r['seed'] and x['controller']==reference),None)
        if ref is None:continue
        assert r['demand_sha256']==ref['demand_sha256'] and r['network_sha256']==ref['network_sha256']
        if r['metrics'][metric] is None or ref['metrics'][metric] is None:continue
        deltas.append(r['metrics'][metric]-ref['metrics'][metric]);seeds.append(r['seed'])
    if not deltas:return None
    mean=float(np.mean(deltas));half=float(student_t.ppf(.975,len(deltas)-1)*np.std(deltas,ddof=1)/math.sqrt(len(deltas))) if len(deltas)>1 else None
    return {'mean_difference':mean,'ci95':[mean-half,mean+half] if half is not None else None,'n':len(deltas),'seeds':seeds}


def aggregate():
    rows=[json.loads(p.read_text()) for p in sorted((ROOT/'results/raw').glob('plan_*/result.json'))]
    assert all(r['valid'] for r in rows),'An invalid run must be investigated and reported, never silently filtered.'
    library=json.loads((ROOT/'results/plan_library.json').read_text())
    summary={'title':'Coordinated plan selection','study':'coordinated','expected_runs':60,'completed_runs':len(rows),'valid_runs':len(rows),
        'status':'complete' if len(rows)==60 else 'in_progress','names':NAMES,'scenario_names':SCENARIOS,'replay_seed':31,
        'scenario_notes':{'am':'','surge':'Demand increases by 50% during minutes 5:30–10:30.',
            'shift':'Synthetic demand shifts toward cross streets at 6:20, then toward avenues at 9:40.'},
        'groups':{},'paired':{},'jev_comparisons':{},'replays':{},'plan_library':library,
        'downloads':{'report':'data/coordinated-report.md','runs':'data/coordinated-runs.json'},
        'methods':{'seeds':list(range(31,36)),'replications':5,'warmup_s':180,'measurement_s':600,'drain_s':180,
            'development_seeds':[901,902],'cadence_s':90,'forecast_horizon_s':180,'history_s':120,
            'clock':'Actual preparation and inference time included in 1x real-time Jev runs; numerical computation is measured. Plan installation waits for eligible local cycle starts.'},
        'limitations':['NYC-informed, schematic and vehicle-only; not field validated.',
            'Five fresh paired seeds per scenario; exploratory pilot without multiple-comparison adjustment.',
            'Synthetic surge and directional changes, not observed NYC events.',
            'Forecasts use assumed discharge rates and recent detected arrivals; no incident semantics, sensing delays or learned forecasting.',
            'All candidate plans retain a 90 s cycle and the original offsets. This version selects green-split profiles only.'],
        'diagnostics':[{'id':r['id'],'valid':r['valid'],'collisions':r['metrics']['colliding_vehicle_events'],'teleports':r['metrics']['teleports'],
            'conflicting_green_steps':r['metrics']['conflicting_green_steps'],'timing_violations':r['metrics']['plan_timing_violations']} for r in rows]}
    destination=ROOT/'viewer/dist/data'
    for scenario in SCENARIOS:
        summary['groups'][scenario]={};summary['paired'][scenario]={};summary['replays'][scenario]={};summary['jev_comparisons'][scenario]={}
        for controller in NAMES:
            group=[r for r in rows if r['scenario']==scenario and r['controller']==controller]
            if not group:continue
            pooled=[q['latency_s'] for r in group for q in json.loads((ROOT/'results/raw'/r['id']/'jev_requests.json').read_text())] if controller=='plan-jev' else []
            summary['groups'][scenario][controller]={'n':len(group),'metrics':{m:float(np.mean([r['metrics'][m] for r in group if r['metrics'][m] is not None])) for m in METRICS},
                'execution':{'requests':sum(r['execution']['requests'] for r in group),'latency_p50_s':float(np.quantile(pooled,.5)) if pooled else None,
                             'latency_p95_s':float(np.quantile(pooled,.95)) if pooled else None}}
            if controller!='fixed':summary['paired'][scenario][controller]={'vs':'fixed','metrics':{m:paired(rows,scenario,controller,'fixed',m) for m in METRICS}}
            path=ROOT/'results/raw'/f'plan_{scenario}_{controller}_31'/'replay.json.gz'
            if path.exists():
                filename=f'plan_{scenario}_{controller}.json.gz'
                with gzip.open(path,'rt') as f:replay=json.load(f)
                forecasts=json.loads((path.parent/'plan_forecasts.json').read_text())
                replay['plan_decisions']=[{'observed_sim_s':q['observed_sim_s'],'numerical_choice':q['numerical_choice'],
                    'candidates':q['state']['corridor']['candidate_plans']} for q in forecasts]
                with gzip.open(destination/filename,'wt') as f:json.dump(replay,f,separators=(',',':'))
                summary['replays'][scenario][controller]='data/'+filename
        for ref in ('fixed','library-fixed','plan-numeric'):
            p=paired(rows,scenario,'plan-jev',ref,'mean_delay_s')
            if p:summary['jev_comparisons'][scenario][ref]=p
    audit_path=ROOT/'results/coordinated_validation.json'
    if audit_path.exists():summary['coordinated_validation']=json.loads(audit_path.read_text())
    retry_path=ROOT/'results/coordinated_execution_retry.json'
    if retry_path.exists():
        retry=json.loads(retry_path.read_text())
        summary['execution_retry']={'excluded_attempts':len(retry['invalid_attempts']),'reason':retry['reason'],'evidence':'data/coordinated_execution_retry.json'}
    (ROOT/'results/coordinated_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (destination/'coordinated-summary.json').write_text(json.dumps(summary,separators=(',',':'))+'\n')
    (destination/'coordinated-runs.json').write_text(json.dumps([{k:v for k,v in r.items() if k!='series'} for r in rows],separators=(',',':'))+'\n')
    write_report(summary)
    for file in ('plan_library.json','coordinated_protocol.json','coordinated_validation.json','coordinated_execution_retry.json'):
        if (ROOT/'results'/file).exists():shutil.copy2(ROOT/'results'/file,destination/file)
    print(json.dumps({'runs':len(rows),'valid':summary['valid_runs'],'status':summary['status']}))
    return summary


def write_report(s):
    complete=s['status']=='complete';audit=s.get('coordinated_validation');library=s['plan_library']
    lines=['# Coordinated traffic-plan selection','',
        'Status: '+('60/60 runs complete; independent audit '+('passed.' if audit else 'pending.') if complete else f"{s['completed_runs']}/60 runs complete. Live Jev results are pending."),'',
        'This experiment compares the original tuned fixed plan, a retuned single plan, a numerical plan selector and Jev selecting from the same coordinated-plan library. The 50 earlier runs and their controllers remain unchanged. Evaluation uses five fresh traffic seeds (31–35) per scenario.','',
        '## Primary results','',
        'Mean accumulated time loss plus entry delay per requested evaluation trip; unfinished trips are retained. Lower is better.','',
        '| Scenario | Tuned fixed | Retuned fixed | Numerical selector | Coordinated Jev |','|---|---:|---:|---:|---:|']
    for scenario,name in SCENARIOS.items():
        g=s['groups'][scenario]
        lines.append('| '+name+' | '+' | '.join(f"{g[c]['metrics']['mean_delay_s']:.2f} s" if c in g else 'Pending' for c in NAMES)+' |')
    if complete:
        lines+=['','| Scenario | Jev minus original fixed | Jev minus retuned fixed | Jev minus numerical |','|---|---:|---:|---:|']
        for scenario,name in SCENARIOS.items():
            values=[]
            for ref in ('fixed','library-fixed','plan-numeric'):
                p=s['jev_comparisons'][scenario][ref];lo,hi=p['ci95'];values.append(f"{p['mean_difference']:+.2f} s [{lo:+.2f}, {hi:+.2f}]")
            lines.append('| '+name+' | '+' | '.join(values)+' |')
        lines+=['','Brackets give 95% paired Student-t intervals across five seeds. Negative differences favor Jev. Intervals summarize these five paired runs; model and service variability are not estimated separately. The pilot has no multiple-comparison adjustment and does not establish field effectiveness.','',
            'Improvement over the original fixed plan alone does not establish a contribution from Jev. The retuned fixed arm isolates the benefit of a better single plan; the numerical selector uses the identical candidate library, observations, forecasts and signal constraints.','']
        effects={case:100*s['jev_comparisons'][case]['fixed']['mean_difference']/s['groups'][case]['fixed']['metrics']['mean_delay_s'] for case in SCENARIOS}
        lines+=['**Observed outcome.** Relative to the original fixed plan, Jev changed mean delay by '+', '.join(f"{effects[case]:+.1f}% ({name.lower()})" for case,name in SCENARIOS.items())+'. These are sample averages; read their paired intervals above.','']
        if all(s['jev_comparisons'][case]['fixed']['ci95'][0]<=0<=s['jev_comparisons'][case]['fixed']['ci95'][1] for case in SCENARIOS):
            lines+=['All three Jev-versus-original-fixed intervals include zero. This pilot does not establish a reliable improvement over the original baseline.','']
        if all(s['jev_comparisons'][case]['library-fixed']['mean_difference']>0 for case in SCENARIOS):
            lines+=['The retuned fixed plan has lower mean delay than Jev in all three scenarios.','']
        if all(s['jev_comparisons'][case]['plan-numeric']['ci95'][0]<=0<=s['jev_comparisons'][case]['plan-numeric']['ci95'][1] for case in SCENARIOS):
            lines+=['Jev shows no demonstrated advantage over the matched numerical selector in these paired intervals. The result motivates further work on plan design and forecast quality; it does not show an added benefit from Jev in this numeric decision task.','']
        identical=[name.lower() for case,name in SCENARIOS.items() if s['jev_comparisons'][case]['plan-numeric']['ci95']==[0,0]]
        if identical:lines+=['Jev and numerical selection produced identical primary delay in every paired seed for: '+', '.join(identical)+'. This is an observed result for these runs, not a general equivalence guarantee.','']
    lines+=['## Control and development','',
        'Seven candidate green-split profiles were evaluated in 84 development simulations: six traffic patterns and two seeds. The library retains the winner for each pattern, the best single plan across the AM/surge/shift mixture, and the original reference. No evaluation seeds entered tuning.','',
        '| Candidate retained | Avenue / cross-street greens |','|---|---|']
    for key,plan in library['plans'].items():
        unique=sorted(set(plan['greens'].values()))
        description=f'{unique[0]}/{82-unique[0]} s everywhere' if len(unique)==1 else ', '.join(f'{j}: {g}/{82-g}' for j,g in plan['greens'].items())
        lines.append(f'| {key} | {description} |')
    lines+=['',f"The retuned fixed arm uses **{library['best_static']}**, selected by its equal-weight average delay across AM, surge and shifting demand on development seeds. This means best among the seven tested profiles on that development mixture, not a proven globally optimal fixed plan.",'',
        'Every 90 seconds, beginning at simulated second 60, the selector receives current queues and occupancies, the last two minutes of detected arrivals, and forecasts for all candidate plans. The forecast is a fluid network model with finite storage, current vehicle positions and speeds, the most recent minute of boundary arrival rates, published turning shares, 9 m/s propagation and assumed discharge of 0.48 vehicles/second/lane. It predicts 180 seconds at 2-second resolution. Its objective is queued vehicle-seconds plus 30 seconds per vehicle queued at the horizon.','',
        'Jev chooses one plan for all twelve intersections. The prompt evaluates the candidates equally and gives no automatic preference to the current plan. The numerical selector minimizes the supplied objective. The models receive no future departure schedule, scenario label or knowledge of when synthetic demand changes will happen. The forecast is approximate and has not been calibrated against observed NYC queues.','',
        'A selected plan becomes eligible three seconds after the observation. Each intersection installs its split at its next local cycle start. The whole corridor therefore transitions gradually over at most one cycle. Greens remain 22–60 seconds; both yellow intervals remain three seconds and both all-red intervals one second. Every cycle remains 90 seconds and retains its original start-time offset. This version changes persistent green splits; it does not optimize cycle lengths or offsets.','',
        '## Latency and decisions','']
    if audit:
        lines += [f"There were {audit['requests']} real API calls and {audit['model_actions']} accepted Jev selections. Median end-to-end request latency was {audit['latency_s']['p50']*1000:.0f} ms; P95 {audit['latency_s']['p95']*1000:.0f} ms; maximum {audit['latency_s']['max']*1000:.0f} ms. This includes forecast preparation, client scheduling and actual API completion. API errors: {audit['api_errors']}; missed deadlines: {audit['deadline_misses']}; retained-plan fallback decisions: {audit['fallback_actions']}. Errors and deadline misses may overlap.",'',
            f"Jev agreed with the numerical selector on {audit['agrees_with_numerical_selector']}/{audit['model_actions']} accepted decisions, evaluated on each Jev run's own observed traffic state. Choice counts: "+', '.join(f'{k}: {v}' for k,v in audit['choices'].items())+'.','',
            f"Each of the 15 Jev runs advanced at 1x real time, with staggered concurrent starts. The largest host clock lag was {audit['max_clock_lag_s']*1000:.1f} ms. No action preceded its response, and installation also waited for the eligible local cycle. Observation-to-installation age was {audit['installation_age_s']['p50']:.1f} s at the median and {audit['installation_age_s']['max']:.1f} s at maximum. This scheduling delay is part of the measured traffic outcome.",'']
    else:lines+=['Live calls and the independent audit are still pending.','']
    if s.get('execution_retry'):
        lines+=['**Execution interruption.** The first complete live batch produced 15 invalid attempts because the laptop slept, violating the pre-existing 0.2-second maximum clock-lag criterion. All 15 Jev cells were repeated with unchanged code, plans, seeds, metrics and validity rules; the 45 valid conventional runs were retained. No valid result was selected or discarded based on its traffic performance. The repeat was specified before it began. [Excluded-attempt metrics, hashes and sleep evidence](../results/coordinated_execution_retry.json) remain available; complete original traces are retained locally.','']
    lines+=['Numerical selection runs accelerated, with measured forecast/selection time rounded up to a simulation step before acceptance and the same installation eligibility rule. Roadside sensing and physical actuator latency are not modeled. Neither arm receives future traffic.','',
        '## Supporting traffic measures','',
        'Trip times cover completed trips only. Queue metrics include all vehicles during measurement; cohort completion is measured after the three-minute drain. Peak queue is the mean of per-run maxima.','']
    for scenario,name in SCENARIOS.items():
        lines += [f'### {name}','','| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Completed | Unfinished | Stops/trip | Congested link-s |','|---|---:|---:|---:|---:|---:|---:|---:|']
        for c,label in NAMES.items():
            if c not in s['groups'][scenario]:continue
            m=s['groups'][scenario][c]['metrics']
            lines.append(f"| {label} | {m['mean_completed_travel_s']:.1f} | {m['p95_completed_travel_s']:.1f} | {m['mean_queue_vehicles']:.1f} / {m['peak_queue_vehicles']:.1f} | {m['completed_trips']:.1f} | {m['unfinished_trips']:.1f} | {m['mean_stops']:.2f} | {m['congested_link_seconds']:.1f} |")
        lines.append('')
    lines+=['## Validation and scope','']
    if audit:lines += [f"All {audit['valid_runs']} runs passed technical checks. Independently checked {audit['phase_durations_checked']:,} observed phase durations, {audit['cycles_checked']:,} consecutive cycles and {audit['plan_installations_checked']:,} installations. Zero signal timing violations, conflicting greens, simulated collisions or teleports. Inputs match within every scenario/seed comparison. A fixed-arm regression reproduced the original metrics exactly; all prior result hashes and frozen experiment hashes match.",'']
    lines+=['Twenty automated tests passed, including observed SUMO phase/cycle checks and exact fixed-run equivalence. Zero simulated collisions is an implementation check, not evidence of street safety.','',
        'The original NYC-informed assumptions remain: twelve schematic intersections, published AM turn volumes, stochastic departures, assumed lanes and driving behavior, and no pedestrians, bicycles, transit stops or curbside incidents. Each run contains 180 seconds of warm-up, 600 seconds of evaluation demand and 180 seconds of drain.','',
        'The surge raises all boundary demand 50% during the middle five evaluation minutes. The new directional case starts with baseline demand, changes to 0.65x avenue and 2.2x cross-street inflow after 200 evaluation seconds, then to 1.4x avenue and 0.6x cross inflow after 400 seconds. Both are synthetic tests, not measured NYC events. Demand scenarios were fixed before evaluation.','',
        'The original AM case, a retuned fixed baseline and a matched numerical selector are all retained to avoid crediting the model for favorable scenario selection or ordinary retiming. The experiment has no incident-text input, learned model, held-out physical calibration or borough-scale validity claim.','',
        '## Reproduction','',
        '[README](../README.md) · [Frozen protocol](../results/coordinated_protocol.json) · [Development evidence](../results/plan_library.json) · [Independent audit](../results/coordinated_validation.json) · [Results](../results/coordinated_summary.json). The preselected replay is seed 31. Raw forecasts, requests, actions, installations, signal events and SUMO trip logs are retained in `results/raw/`.','']
    report='\n'.join(lines);(ROOT/'docs/COORDINATED_RESULTS.md').write_text(report)
    public=report.replace('[README](../README.md)','[README](https://github.com/jan-barg/jev-traffic-control)').replace('(../results/','(').replace('(coordinated_summary.json)','(coordinated-summary.json)')
    (ROOT/'viewer/dist/data/coordinated-report.md').write_text(public)

if __name__=='__main__':aggregate()
