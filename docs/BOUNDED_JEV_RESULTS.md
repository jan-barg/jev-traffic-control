# Midtown traffic-signal experiment: bounded Jev

This exploratory extension adds ten live bounded-Jev runs to the original forty-run pilot. Native Jev, its code and its recorded results are preserved in [version 1](https://github.com/jan-barg/jev-traffic-control/tree/v1.0.0). The new policy was frozen before these ten runs, after the original results were known. It uses the same traffic seeds for a direct comparison; this is not a new held-out confirmation study.

## Controller

The reference has a coordinated 90-second cycle. Once per local cycle, Jev selects one of three avenue/cross-street green splits: 47/35, 52/30 or 57/25 seconds. The middle choice keeps the reference plan. Each change transfers five seconds between the two greens; it never accumulates across cycles. Three-second yellow, one-second all-red, cycle length and the original coordination offsets are retained.

The request is made 30–40 seconds into avenue green. Its observations include current queues, lane counts, vehicles, downstream space and an arrival estimate for the next 15 seconds based only on current vehicle positions and speeds. It has no access to future departures. A late or failed request retains the baseline split. Native Jev continues to use its original hold/switch policy and queue-pressure fallback.

## Primary result

Delay is accumulated SUMO time loss plus insertion delay per requested evaluation trip, including unfinished trips. Values are means over five paired seeds. Lower is better.

| Demand | Fixed | Actuated | Queue pressure | Native Jev | Bounded Jev | Bounded − fixed, 95% paired interval |
|---|---:|---:|---:|---:|---:|---:|
| Weekday morning | 40.37 s | 61.67 s | 59.91 s | 89.45 s | 40.39 s | +0.02 s [-0.01, +0.06] |
| 50% surge | 46.95 s | 87.37 s | 77.02 s | 143.12 s | 46.95 s | +0.00 s [+0.00, +0.00] |

The intervals use a paired Student-t calculation across five traffic seeds. They measure variation within this simulation and omit uncertainty in physical assumptions and actual NYC operation. Secondary metrics are descriptive, with no multiple-comparison adjustment.

**Weekday morning:** bounded Jev has 0.1% higher mean delay than fixed timing (+0.02 seconds per trip). The interval includes zero, so this pilot does not resolve a difference from fixed timing. Its paired difference from native Jev is -49.06 seconds [-60.76, -37.35].

**50% surge:** bounded Jev exactly matches fixed timing in every seed. A zero-width sample interval here reflects identical observed results, not proof of equivalence under other conditions. Its paired difference from native Jev is -96.17 seconds [-108.60, -83.73].

**Interpretation:** Jev kept the baseline for 1,254 of 1,256 applied decisions. This policy mostly reproduced the coordinated fixed plan and provides no evidence of an improvement over it. The preselected seed-11 replay can therefore look identical to the fixed view; it is an actual recorded outcome.

The comparison with native Jev changes both the action policy and coordination design. It cannot isolate the contribution of model intelligence from the benefit of retaining the coordinated plan. The fixed arm is the relevant control for whether these bounded model decisions improve that plan.

## Supporting measures

Travel-time statistics include completed trips only. Completion and unfinished counts refer to the evaluation cohort after the three-minute drain. Mean queue covers all vehicles during measurement; peak queue is the mean of per-run maxima.

### Weekday morning

| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Completed at demand end | Completed after drain | Unfinished | Stops/trip | Congested link-s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tuned fixed-time | 104.7 | 174.9 | 29.6 / 61.8 | 554.0 | 689.0 | 4.0 | 1.14 | 2.9 |
| Actuated | 125.2 | 214.3 | 48.2 / 97.0 | 547.2 | 685.2 | 7.8 | 2.12 | 374.7 |
| Queue pressure | 124.1 | 195.2 | 44.0 / 83.4 | 549.0 | 687.6 | 5.4 | 2.38 | 95.0 |
| Jev | 153.0 | 259.5 | 74.0 / 149.8 | 499.4 | 681.2 | 11.8 | 2.46 | 652.9 |
| Bounded Jev | 104.7 | 173.9 | 29.6 / 62.4 | 554.0 | 689.0 | 4.0 | 1.14 | 2.9 |

### 50% surge

| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Completed at demand end | Completed after drain | Unfinished | Stops/trip | Congested link-s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tuned fixed-time | 111.5 | 196.4 | 40.8 / 86.0 | 709.0 | 870.4 | 5.4 | 1.22 | 45.6 |
| Actuated | 146.9 | 295.5 | 74.3 / 163.6 | 649.0 | 844.0 | 31.8 | 2.37 | 667.6 |
| Queue pressure | 140.8 | 234.0 | 66.9 / 147.8 | 669.4 | 862.8 | 13.0 | 2.74 | 435.2 |
| Jev | 188.0 | 378.4 | 120.9 / 278.4 | 528.6 | 750.8 | 125.0 | 3.20 | 1358.3 |
| Bounded Jev | 111.5 | 196.4 | 40.8 / 86.0 | 709.0 | 870.4 | 5.4 | 1.22 | 45.6 |

Congested link-seconds are an occupancy-based spillback proxy, not an observed queue-tail measurement. Delay is measured through minute 16; unfinished trips can incur more delay afterward.

## Real-time inference

The bounded arm made 630 actual API batches and applied 1,256 model choices. Request latency was 473 ms at the median, 681 ms at P95, 953 ms at P99 and 4108 ms maximum. API errors: 1; missed request deadlines: 2; fallback intersection choices: 4. Errors and deadline misses can overlap for the same request.

| Bounded model choice | Applied count |
|---|---:|
| 57/25 s: five seconds to avenue | 0 |
| 52/30 s: keep baseline | 1,254 |
| 47/35 s: five seconds to cross street | 2 |

Each simulation ran at one simulated second per wall second while traffic continued during inference. A response was applied only after actual completion and the next 0.2-second polling step. The maximum host clock lag was 27.3 ms. Ten bounded replications ran concurrently, in a separate batch from native Jev; latency includes the load and service conditions during that batch. Roadside sensor and physical actuator delays remain unmodeled. Replay speed affects display only.

## Validation

- All 50 primary runs passed runtime validity checks; all 10 bounded runs passed the independent audit.
- Independently checked 7,540 observed phase durations and 1,180 successive 90-second cycles; zero bounded timing violations.
- Confirmed clearance order, allowed green splits, one accepted choice per local cycle, original cycle anchors and no application before a response arrived.
- Confirmed identical demand and network inputs for paired runs, vehicle conservation, and no collisions, teleports or conflicting greens.
- A full-horizon keep-only regression reproduced every original fixed-arm metric exactly. This verifies that the new runner itself does not change the reference traffic.
- All frozen bounded source hashes and all forty original result hashes still match. Original native-controller source is unchanged.
- Fourteen automated tests passed, including real SUMO tests of all three allowed choices and the keep-only equivalence check.

These are implementation and reproducibility checks. Zero simulated collisions does not establish street safety. The original in-sample turning-count check and conventional sensitivity results are preserved in the [original report](BENCHMARK_RESULTS.md); bounded Jev has not been evaluated across those physical sensitivity variants.

## Scope

Twelve schematic intersections cover Sixth and Seventh Avenues at West 25th–30th Streets. Forty-eight published AM turning counts inform stochastic departures and turn routes. The fixed plan was tuned on separate development seeds, but is not a verified NYC DOT signal plan. Each run has 180 seconds of warm-up, 600 seconds of measured demand and 180 seconds of drain. Surge adds 50% boundary demand during the middle five minutes.

Lanes, block lengths, fleet mix and driver behavior are assumptions. Pedestrians, bicycles, bus stops and curbside obstruction are absent. No independently observed NYC travel times or queues have been used for field validation. Before claiming street benefits, obtain these observations, actual signal plans and geometry, calibrate the model, and confirm a frozen policy on new held-out conditions.

## Reproduction

See the [README](../README.md), [bounded protocol](../results/bounded_protocol.json), [bounded audit](../results/bounded_validation.json) and [all results](../results/summary.json). Raw request, action, phase-transition and trip logs remain locally in `results/raw/`. Seed 11 was selected for replay before evaluation.

[NYC study record](https://zap.planning.nyc.gov/projects/2024M0142) · [SUMO trip metrics](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html) · [TypeSafe documentation](https://docs.typesafe.ai/)
