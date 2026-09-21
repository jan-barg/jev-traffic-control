"""Report the frozen exploratory bounded-Jev extension without replacing v1 evidence."""
import json
import math
import shutil
import numpy as np
from scipy.stats import t as student_t
from .scenario import ROOT


def paired_difference(runs, scenario, reference):
    rows=[r for r in runs if r['scenario']==scenario and r['controller']=='bounded-jev']
    differences=[]
    for row in rows:
        ref=next(r for r in runs if r['scenario']==scenario and r['controller']==reference and r['seed']==row['seed'])
        assert row['valid'] and ref['valid'] and row['demand_sha256']==ref['demand_sha256']
        differences.append(row['metrics']['mean_delay_s']-ref['metrics']['mean_delay_s'])
    mean=float(np.mean(differences))
    half=float(student_t.ppf(.975,len(differences)-1)*np.std(differences,ddof=1)/math.sqrt(len(differences)))
    return mean,mean-half,mean+half


def write_report(summary,runs):
    assert summary['status']=='complete' and summary['valid_runs']==50
    audit=summary['bounded_validation']
    names=summary['names']
    lines=['# Midtown traffic-signal experiment: bounded Jev','',
        'This exploratory extension adds ten live bounded-Jev runs to the original forty-run pilot. Native Jev, its code and its recorded results are preserved in [version 1](https://github.com/jan-barg/jev-traffic-control/tree/v1.0.0). The new policy was frozen before these ten runs, after the original results were known. It uses the same traffic seeds for a direct comparison; this is not a new held-out confirmation study.','',
        '## Controller','',
        'The reference has a coordinated 90-second cycle. Once per local cycle, Jev selects one of three avenue/cross-street green splits: 47/35, 52/30 or 57/25 seconds. The middle choice keeps the reference plan. Each change transfers five seconds between the two greens; it never accumulates across cycles. Three-second yellow, one-second all-red, cycle length and the original coordination offsets are retained.','',
        'The request is made 30–40 seconds into avenue green. Its observations include current queues, lane counts, vehicles, downstream space and an arrival estimate for the next 15 seconds based only on current vehicle positions and speeds. It has no access to future departures. A late or failed request retains the baseline split. Native Jev continues to use its original hold/switch policy and queue-pressure fallback.','',
        '## Primary result','',
        'Delay is accumulated SUMO time loss plus insertion delay per requested evaluation trip, including unfinished trips. Values are means over five paired seeds. Lower is better.','',
        '| Demand | Fixed | Actuated | Queue pressure | Native Jev | Bounded Jev | Bounded − fixed, 95% paired interval |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for scenario,title in [('am','Weekday morning'),('surge','50% surge')]:
        group=summary['groups'][scenario]
        delta,lo,hi=paired_difference(runs,scenario,'fixed')
        lines.append('| '+title+' | '+' | '.join(f"{group[c]['metrics']['mean_delay_s']:.2f} s" for c in names)+f' | {delta:+.2f} s [{lo:+.2f}, {hi:+.2f}] |')
    lines+=['','The intervals use a paired Student-t calculation across five traffic seeds. They measure variation within this simulation and omit uncertainty in physical assumptions and actual NYC operation. Secondary metrics are descriptive, with no multiple-comparison adjustment.','']
    for scenario,title in [('am','Weekday morning'),('surge','50% surge')]:
        delta,lo,hi=paired_difference(runs,scenario,'fixed')
        pct=100*delta/summary['groups'][scenario]['fixed']['metrics']['mean_delay_s']
        native,nlo,nhi=paired_difference(runs,scenario,'jev')
        finding='lower' if delta<0 else 'higher'
        qualifier=' The interval includes zero, so this pilot does not resolve a difference from fixed timing.' if lo<=0<=hi else ''
        comparison=f'bounded Jev has {abs(pct):.1f}% {finding} mean delay than fixed timing ({delta:+.2f} seconds per trip).{qualifier}' if abs(delta)>1e-9 else 'bounded Jev exactly matches fixed timing in every seed. A zero-width sample interval here reflects identical observed results, not proof of equivalence under other conditions.'
        lines.append(f'**{title}:** {comparison} Its paired difference from native Jev is {native:+.2f} seconds [{nlo:+.2f}, {nhi:+.2f}].')
        lines.append('')
    lines+=[f"**Interpretation:** Jev kept the baseline for {audit['choices'].get('keep',0):,} of {audit['model_actions_applied']:,} applied decisions. This policy mostly reproduced the coordinated fixed plan and provides no evidence of an improvement over it. The preselected seed-11 replay can therefore look identical to the fixed view; it is an actual recorded outcome.",'',
        'The comparison with native Jev changes both the action policy and coordination design. It cannot isolate the contribution of model intelligence from the benefit of retaining the coordinated plan. The fixed arm is the relevant control for whether these bounded model decisions improve that plan.','',
        '## Supporting measures','',
        'Travel-time statistics include completed trips only. Completion and unfinished counts refer to the evaluation cohort after the three-minute drain. Mean queue covers all vehicles during measurement; peak queue is the mean of per-run maxima.','']
    for scenario,title in [('am','Weekday morning'),('surge','50% surge')]:
        lines += [f'### {title}','','| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Completed at demand end | Completed after drain | Unfinished | Stops/trip | Congested link-s |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for controller,name in names.items():
            m=summary['groups'][scenario][controller]['metrics']
            lines.append(f"| {name} | {m['mean_completed_travel_s']:.1f} | {m['p95_completed_travel_s']:.1f} | {m['mean_queue_vehicles']:.1f} / {m['peak_queue_vehicles']:.1f} | {m['completed_by_demand_end']:.1f} | {m['completed_trips']:.1f} | {m['unfinished_trips']:.1f} | {m['mean_stops']:.2f} | {m['congested_link_seconds']:.1f} |")
        lines.append('')
    lines+=['Congested link-seconds are an occupancy-based spillback proxy, not an observed queue-tail measurement. Delay is measured through minute 16; unfinished trips can incur more delay afterward.','',
        '## Real-time inference','',
        f"The bounded arm made {audit['requests']:,} actual API batches and applied {audit['model_actions_applied']:,} model choices. Request latency was {audit['latency_s']['p50']*1000:.0f} ms at the median, {audit['latency_s']['p95']*1000:.0f} ms at P95, {audit['latency_s']['p99']*1000:.0f} ms at P99 and {audit['latency_s']['max']*1000:.0f} ms maximum. API errors: {audit['api_errors']}; missed request deadlines: {audit['deadline_misses']}; fallback intersection choices: {audit['fallback_actions']}. Errors and deadline misses can overlap for the same request.",'',
        '| Bounded model choice | Applied count |','|---|---:|']
    for key,label in [('avenue_plus_5','57/25 s: five seconds to avenue'),('keep','52/30 s: keep baseline'),('cross_plus_5','47/35 s: five seconds to cross street')]:
        lines.append(f"| {label} | {audit['choices'].get(key,0):,} |")
    lines+=['',
        f"Each simulation ran at one simulated second per wall second while traffic continued during inference. A response was applied only after actual completion and the next 0.2-second polling step. The maximum host clock lag was {audit['max_clock_lag_s']*1000:.1f} ms. Ten bounded replications ran concurrently, in a separate batch from native Jev; latency includes the load and service conditions during that batch. Roadside sensor and physical actuator delays remain unmodeled. Replay speed affects display only.",'',
        '## Validation','',
        f"- All 50 primary runs passed runtime validity checks; all {audit['valid_runs']} bounded runs passed the independent audit.",
        f"- Independently checked {audit['phase_durations_checked']:,} observed phase durations and {audit['consecutive_cycles_checked']:,} successive 90-second cycles; zero bounded timing violations.",
        '- Confirmed clearance order, allowed green splits, one accepted choice per local cycle, original cycle anchors and no application before a response arrived.',
        '- Confirmed identical demand and network inputs for paired runs, vehicle conservation, and no collisions, teleports or conflicting greens.',
        '- A full-horizon keep-only regression reproduced every original fixed-arm metric exactly. This verifies that the new runner itself does not change the reference traffic.',
        '- All frozen bounded source hashes and all forty original result hashes still match. Original native-controller source is unchanged.',
        '- Fourteen automated tests passed, including real SUMO tests of all three allowed choices and the keep-only equivalence check.','',
        'These are implementation and reproducibility checks. Zero simulated collisions does not establish street safety. The original in-sample turning-count check and conventional sensitivity results are preserved in the [original report](BENCHMARK_RESULTS.md); bounded Jev has not been evaluated across those physical sensitivity variants.','',
        '## Scope','',
        'Twelve schematic intersections cover Sixth and Seventh Avenues at West 25th–30th Streets. Forty-eight published AM turning counts inform stochastic departures and turn routes. The fixed plan was tuned on separate development seeds, but is not a verified NYC DOT signal plan. Each run has 180 seconds of warm-up, 600 seconds of measured demand and 180 seconds of drain. Surge adds 50% boundary demand during the middle five minutes.','',
        'Lanes, block lengths, fleet mix and driver behavior are assumptions. Pedestrians, bicycles, bus stops and curbside obstruction are absent. No independently observed NYC travel times or queues have been used for field validation. Before claiming street benefits, obtain these observations, actual signal plans and geometry, calibrate the model, and confirm a frozen policy on new held-out conditions.','',
        '## Reproduction','',
        'See the [README](../README.md), [bounded protocol](../results/bounded_protocol.json), [bounded audit](../results/bounded_validation.json) and [all results](../results/summary.json). Raw request, action, phase-transition and trip logs remain locally in `results/raw/`. Seed 11 was selected for replay before evaluation.','',
        '[NYC study record](https://zap.planning.nyc.gov/projects/2024M0142) · [SUMO trip metrics](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html) · [TypeSafe documentation](https://docs.typesafe.ai/)','']
    report='\n'.join(lines)
    (ROOT/'docs/BOUNDED_JEV_RESULTS.md').write_text(report)
    destination=ROOT/'viewer/dist/data'
    public=report.replace('[README](../README.md)','[README](https://github.com/jan-barg/jev-traffic-control)').replace('(../results/','(').replace('(BENCHMARK_RESULTS.md)','(native-report.md)')
    (destination/'benchmark-report.md').write_text(public)
    native=(ROOT/'docs/BENCHMARK_RESULTS.md').read_text().replace('[README](../README.md)','[README](https://github.com/jan-barg/jev-traffic-control/tree/v1.0.0)').replace('(../results/','(').replace(' · [NYC data audit](NYC_BENCHMARK_AUDIT.md)','')
    (destination/'native-report.md').write_text(native)
    for filename in ('validation.json','protocol.json','bounded_protocol.json','bounded_validation.json'):
        shutil.copy2(ROOT/'results'/filename,destination/filename)
