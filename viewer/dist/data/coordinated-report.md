# Coordinated traffic-plan selection

Status: 60/60 runs complete; independent audit passed.

This experiment compares the original tuned fixed plan, a retuned single plan, a numerical plan selector and Jev selecting from the same coordinated-plan library. The 50 earlier runs and their controllers remain unchanged. Evaluation uses five fresh traffic seeds (31–35) per scenario.

## Primary results

Mean accumulated time loss plus entry delay per requested evaluation trip; unfinished trips are retained. Lower is better.

| Scenario | Tuned fixed | Retuned fixed | Numerical selector | Coordinated Jev |
|---|---:|---:|---:|---:|
| Weekday morning | 39.33 s | 39.40 s | 40.34 s | 40.29 s |
| Morning + 50% surge | 44.53 s | 42.52 s | 43.63 s | 43.37 s |
| Changing directional demand | 52.34 s | 45.44 s | 46.84 s | 46.84 s |

| Scenario | Jev minus original fixed | Jev minus retuned fixed | Jev minus numerical |
|---|---:|---:|---:|
| Weekday morning | +0.96 s [-0.44, +2.36] | +0.89 s [+0.04, +1.73] | -0.05 s [-0.22, +0.11] |
| Morning + 50% surge | -1.17 s [-3.28, +0.95] | +0.85 s [-0.41, +2.11] | -0.27 s [-1.05, +0.52] |
| Changing directional demand | -5.50 s [-12.66, +1.66] | +1.40 s [-2.34, +5.14] | +0.00 s [+0.00, +0.00] |

Brackets give 95% paired Student-t intervals across five seeds. Negative differences favor Jev. Intervals summarize these five paired runs; model and service variability are not estimated separately. The pilot has no multiple-comparison adjustment and does not establish field effectiveness.

Improvement over the original fixed plan alone does not establish a contribution from Jev. The retuned fixed arm isolates the benefit of a better single plan; the numerical selector uses the identical candidate library, observations, forecasts and signal constraints.

**Observed outcome.** Relative to the original fixed plan, Jev changed mean delay by +2.4% (weekday morning), -2.6% (morning + 50% surge), -10.5% (changing directional demand). These are sample averages; read their paired intervals above.

All three Jev-versus-original-fixed intervals include zero. This pilot does not establish a reliable improvement over the original baseline.

The retuned fixed plan has lower mean delay than Jev in all three scenarios.

Jev shows no demonstrated advantage over the matched numerical selector in these paired intervals. The result motivates further work on plan design and forecast quality; it does not show an added benefit from Jev in this numeric decision task.

Jev and numerical selection produced identical primary delay in every paired seed for: changing directional demand. This is an observed result for these runs, not a general equivalence guarantee.

## Control and development

Seven candidate green-split profiles were evaluated in 84 development simulations: six traffic patterns and two seeds. The library retains the winner for each pattern, the best single plan across the AM/surge/shift mixture, and the original reference. No evaluation seeds entered tuning.

| Candidate retained | Avenue / cross-street greens |
|---|---|
| g30 | 30/52 s everywhere |
| g52 | 52/30 s everywhere |
| g60 | 60/22 s everywhere |
| flow | 7_30: 34/48, 7_29: 40/42, 7_28: 40/42, 7_27: 54/28, 7_26: 44/38, 7_25: 48/34, 6_30: 42/40, 6_29: 54/28, 6_28: 46/36, 6_27: 50/32, 6_26: 48/34, 6_25: 56/26 |
| cross_flow | 7_30: 26/56, 7_29: 32/50, 7_28: 32/50, 7_27: 46/36, 7_26: 36/46, 7_25: 40/42, 6_30: 34/48, 6_29: 48/34, 6_28: 38/44, 6_27: 40/42, 6_26: 40/42, 6_25: 48/34 |

The retuned fixed arm uses **flow**, selected by its equal-weight average delay across AM, surge and shifting demand on development seeds. This means best among the seven tested profiles on that development mixture, not a proven globally optimal fixed plan.

Every 90 seconds, beginning at simulated second 60, the selector receives current queues and occupancies, the last two minutes of detected arrivals, and forecasts for all candidate plans. The forecast is a fluid network model with finite storage, current vehicle positions and speeds, the most recent minute of boundary arrival rates, published turning shares, 9 m/s propagation and assumed discharge of 0.48 vehicles/second/lane. It predicts 180 seconds at 2-second resolution. Its objective is queued vehicle-seconds plus 30 seconds per vehicle queued at the horizon.

Jev chooses one plan for all twelve intersections. The prompt evaluates the candidates equally and gives no automatic preference to the current plan. The numerical selector minimizes the supplied objective. The models receive no future departure schedule, scenario label or knowledge of when synthetic demand changes will happen. The forecast is approximate and has not been calibrated against observed NYC queues.

A selected plan becomes eligible three seconds after the observation. Each intersection installs its split at its next local cycle start. The whole corridor therefore transitions gradually over at most one cycle. Greens remain 22–60 seconds; both yellow intervals remain three seconds and both all-red intervals one second. Every cycle remains 90 seconds and retains its original start-time offset. This version changes persistent green splits; it does not optimize cycle lengths or offsets.

## Latency and decisions

There were 150 real API calls and 150 accepted Jev selections. Median end-to-end request latency was 412 ms; P95 552 ms; maximum 752 ms. This includes forecast preparation, client scheduling and actual API completion. API errors: 0; missed deadlines: 0; retained-plan fallback decisions: 0. Errors and deadline misses may overlap.

Jev agreed with the numerical selector on 145/150 accepted decisions, evaluated on each Jev run's own observed traffic state. Choice counts: flow: 43, g60: 15, cross_flow: 27, g52: 32, g30: 33.

Each of the 15 Jev runs advanced at 1x real time, with staggered concurrent starts. The largest host clock lag was 20.7 ms. No action preceded its response, and installation also waited for the eligible local cycle. Observation-to-installation age was 52.3 s at the median and 74.6 s at maximum. This scheduling delay is part of the measured traffic outcome.

**Execution interruption.** The first complete live batch produced 15 invalid attempts because the laptop slept, violating the pre-existing 0.2-second maximum clock-lag criterion. All 15 Jev cells were repeated with unchanged code, plans, seeds, metrics and validity rules; the 45 valid conventional runs were retained. No valid result was selected or discarded based on its traffic performance. The repeat was specified before it began. [Excluded-attempt metrics, hashes and sleep evidence](coordinated_execution_retry.json) remain available; complete original traces are retained locally.

Numerical selection runs accelerated, with measured forecast/selection time rounded up to a simulation step before acceptance and the same installation eligibility rule. Roadside sensing and physical actuator latency are not modeled. Neither arm receives future traffic.

## Supporting traffic measures

Trip times cover completed trips only. Queue metrics include all vehicles during measurement; cohort completion is measured after the three-minute drain. Peak queue is the mean of per-run maxima.

### Weekday morning

| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Completed | Unfinished | Stops/trip | Congested link-s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tuned fixed-time | 104.4 | 176.6 | 28.9 / 57.8 | 701.8 | 3.8 | 1.11 | 0.2 |
| Retuned fixed plan | 104.4 | 175.6 | 28.7 / 63.2 | 701.6 | 4.0 | 1.08 | 0.5 |
| Numerical plan selector | 105.3 | 176.9 | 29.6 / 65.2 | 701.4 | 4.2 | 1.09 | 0.5 |
| Coordinated Jev | 105.2 | 176.9 | 29.5 / 64.4 | 701.4 | 4.2 | 1.09 | 0.5 |

### Morning + 50% surge

| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Completed | Unfinished | Stops/trip | Congested link-s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tuned fixed-time | 109.3 | 187.7 | 38.8 / 76.4 | 848.6 | 4.6 | 1.18 | 35.2 |
| Retuned fixed plan | 107.3 | 178.4 | 36.2 / 87.2 | 848.6 | 4.6 | 1.12 | 1.8 |
| Numerical plan selector | 108.4 | 181.5 | 37.4 / 86.6 | 848.6 | 4.6 | 1.14 | 14.3 |
| Coordinated Jev | 108.1 | 179.9 | 37.1 / 86.0 | 848.6 | 4.6 | 1.14 | 10.8 |

### Changing directional demand

| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Completed | Unfinished | Stops/trip | Congested link-s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tuned fixed-time | 116.9 | 211.2 | 41.3 / 94.4 | 774.4 | 5.2 | 1.30 | 189.0 |
| Retuned fixed plan | 110.3 | 184.8 | 36.0 / 73.0 | 775.8 | 3.8 | 1.19 | 39.8 |
| Numerical plan selector | 111.5 | 190.9 | 36.9 / 75.8 | 774.8 | 4.8 | 1.21 | 26.0 |
| Coordinated Jev | 111.5 | 190.9 | 36.9 / 75.8 | 774.8 | 4.8 | 1.21 | 26.0 |

## Validation and scope

All 60 runs passed technical checks. Independently checked 45,780 observed phase durations, 7,080 consecutive cycles and 7,800 installations. Zero signal timing violations, conflicting greens, simulated collisions or teleports. Inputs match within every scenario/seed comparison. A fixed-arm regression reproduced the original metrics exactly; all prior result hashes and frozen experiment hashes match.

Twenty automated tests passed, including observed SUMO phase/cycle checks and exact fixed-run equivalence. Zero simulated collisions is an implementation check, not evidence of street safety.

The original NYC-informed assumptions remain: twelve schematic intersections, published AM turn volumes, stochastic departures, assumed lanes and driving behavior, and no pedestrians, bicycles, transit stops or curbside incidents. Each run contains 180 seconds of warm-up, 600 seconds of evaluation demand and 180 seconds of drain.

The surge raises all boundary demand 50% during the middle five evaluation minutes. The new directional case starts with baseline demand, changes to 0.65x avenue and 2.2x cross-street inflow after 200 evaluation seconds, then to 1.4x avenue and 0.6x cross inflow after 400 seconds. Both are synthetic tests, not measured NYC events. Demand scenarios were fixed before evaluation.

The original AM case, a retuned fixed baseline and a matched numerical selector are all retained to avoid crediting the model for favorable scenario selection or ordinary retiming. The experiment has no incident-text input, learned model, held-out physical calibration or borough-scale validity claim.

## Reproduction

[README](https://github.com/jan-barg/jev-traffic-control) · [Frozen protocol](coordinated_protocol.json) · [Development evidence](plan_library.json) · [Independent audit](coordinated_validation.json) · [Results](coordinated-summary.json). The preselected replay is seed 31. Raw forecasts, requests, actions, installations, signal events and SUMO trip logs are retained in `results/raw/`.
